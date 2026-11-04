// Запуск приложения: язык, вход через Telegram, оболочка (шапка, разделы, навигация), экраны входа и ошибок.
import { applyLanguage, initI18n, language, LANGUAGE_NAMES, t } from './i18n.js';
import { createApi } from './api.js';
import { telegram } from './telegram.js';
import { initTheme, setTheme, themeChoice } from './theme.js';
import { app, nav } from './state.js';
import { loadHouses, redraw, refresh, selectHouse, subscribe } from './data.js';
import { button, closeAllSheets, closeTopSheet, configureUi, confirmSheet, errorText, fail, h, icon, openSheet, openSheetCount, skeleton } from './ui.js';
import { renderHome } from './views/home.js';
import { createHistory } from './views/history.js';
import { renderHouse } from './views/house.js';
import { renderOnboarding } from './views/onboarding.js';
import { hasDrafts } from './views/form.js';
import { hasPendingReceipts } from './views/receipts.js';
import { hasPendingImport } from './views/files.js';

const CONTEXT_KEY = 'domovoy.language-context';
const STALE_AFTER_MS = 60000;
const TABS = [['home', 'home'], ['history', 'clock'], ['house', 'people']];
const root = document.getElementById('app');
let shell = null;
let shownHouse;
let loadedAt = Date.now();
let expired = false;
let wired = false;

const hasUnsaved = () => hasDrafts() || hasPendingReceipts() || hasPendingImport();

// ── Экраны вне оболочки ───────────────────────────────────────────────────────────────────────────

function languagePill() {
  return h('button', { type: 'button', class: 'pill', 'aria-haspopup': 'dialog', 'aria-label': t("Язык и тема"), onClick: openAppearance },
    icon('globe'), language.toUpperCase());
}

function standalone(...content) {
  shell = null;
  root.replaceChildren(h('main', { class: 'gate', id: 'main' }, h('div', { class: 'gate-top' }, languagePill()), ...content));
}

function showGate() {
  document.title = t("Закрытое приложение");
  standalone(h('span', { class: 'gate-mark', 'aria-hidden': 'true' }, icon('home')), h('h1', {}, t("Вход в приложение")),
    h('p', { class: 'gate-text' }, t("Откройте эту страницу из личного чата, где вы получили ссылку.")));
}

function showExpired() {
  expired = true; // закрывающиеся листы ещё вызовут перерисовку — она не должна стереть этот экран
  closeAllSheets();
  standalone(h('span', { class: 'gate-mark', 'aria-hidden': 'true' }, icon('clock')), h('h1', {}, t("Сеанс закончился")),
    h('p', { class: 'gate-text' }, t("Закройте приложение и откройте его снова из чата с ботом — так вход обновится.")),
    button({ label: t("Закрыть приложение"), onClick: () => telegram.close() }));
}

function showBootError(error) {
  standalone(h('span', { class: 'gate-mark', 'aria-hidden': 'true' }, icon('alert')), h('h1', {}, t("Не получилось открыть")),
    h('p', { class: 'gate-text' }, errorText(error)), button({ label: t("Попробовать ещё раз"), onClick: () => boot() }));
}

function showOnboarding() {
  standalone();
  const main = root.firstElementChild;
  const page = h('div', { class: 'welcome-wrap' });
  main.append(page);
  renderOnboarding(page, { initialName: telegram.user?.first_name || '', onDone: houseId => loadHouses(houseId) });
}

// ── Листы шапки: язык и тема, дом ─────────────────────────────────────────────────────────────────

async function requestLanguage(next) {
  if (next === language) return;
  const agreed = !hasUnsaved() || await confirmSheet({ title: t("Сменить язык?"), confirmLabel: t("Сменить язык"),
    text: t("Смена языка перезагрузит страницу. Несохранённый ввод и черновики будут потеряны. Продолжить?") });
  if (agreed) applyLanguage(next);
}

function radioRow({ title, mark, checked, onClick }) {
  return h('button', { type: 'button', class: 'group-row', role: 'radio', 'aria-checked': String(checked), onClick },
    h('span', { class: 'row-icon', 'aria-hidden': 'true' }, mark),
    h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, title)), icon('check', 'row-check'));
}

// Тема меняется сразу, без перезагрузки; язык — с перезагрузкой, поэтому лист закрывается.
function openAppearance() {
  const themes = [['auto', telegram.available ? t("Как в Telegram") : t("Как в системе"), 'contrast'], ['light', t("Светлая"), 'sun'], ['dark', t("Тёмная"), 'moon']];
  const themeRows = themes.map(([choice, title, iconName]) => radioRow({ title, mark: icon(iconName), checked: choice === themeChoice, onClick: () => {
    if (choice === themeChoice) return;
    setTheme(choice);
    telegram.haptic.select();
    themeRows.forEach((row, index) => row.setAttribute('aria-checked', String(themes[index][0] === choice)));
  } }));
  const sheet = openSheet({ title: t("Язык и тема"), size: 'sm', body: [
    h('section', { class: 'sheet-section' }, h('h3', { id: 'theme-title' }, t("Тема")),
      h('div', { class: 'group', role: 'radiogroup', 'aria-labelledby': 'theme-title' }, themeRows)),
    h('section', { class: 'sheet-section' }, h('h3', { id: 'language-title' }, t("Язык")),
      h('div', { class: 'group', role: 'radiogroup', 'aria-labelledby': 'language-title' },
        Object.entries(LANGUAGE_NAMES).map(([code, name]) => radioRow({ title: name, mark: h('span', { class: 'row-code' }, code.toUpperCase()), checked: code === language,
          onClick: () => { sheet.close(); requestLanguage(code); } })))),
  ] });
}

function openHouses() {
  const sheet = openSheet({ title: t("В каком вы доме?"), size: 'sm', body: [
    h('div', { class: 'group' }, app.houses.map(house => h('button', { type: 'button', class: 'group-row', 'aria-current': house.id === app.houseId ? 'true' : undefined,
      onClick: async () => {
        sheet.close();
        if (house.id === app.houseId) return;
        try { await selectHouse(house.id); } catch (error) { fail(error); }
      } },
    h('span', { class: 'row-icon' }, icon('home')),
    h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, house.name),
      h('span', { class: 'row-meta' }, house.role === 'owner' ? t("Владелец дома") : t("Жилец"))),
    house.id === app.houseId ? icon('check', 'row-check') : null))),
    button({ label: t("Создать дом или вступить"), icon: 'plus', variant: 'secondary', block: true, onClick: () => { sheet.close(); nav.go('house', 'add'); } }),
  ] });
}

// ── Оболочка ──────────────────────────────────────────────────────────────────────────────────────

function tabs(className) {
  const labels = { home: t("Главная"), history: t("История"), house: t("Дом") };
  return h('nav', { class: className, 'aria-label': t("Основная навигация") }, TABS.map(([view, iconName]) =>
    h('button', { type: 'button', class: 'tab', dataset: { view }, onClick: () => go(view) }, icon(iconName), h('span', {}, labels[view]))));
}

function buildShell() {
  const views = { home: h('section', { class: 'view', id: 'view-home' }), history: h('section', { class: 'view', id: 'view-history', hidden: true }),
    house: h('section', { class: 'view', id: 'view-house', hidden: true }) };
  const banner = h('p', { class: 'banner', role: 'status', hidden: navigator.onLine }, icon('alert'),
    t("Нет сети. Ваш ввод останется в форме. Попробуйте сохранить, когда связь вернётся."));
  const bars = [tabs('tabbar'), tabs('topnav')];
  root.replaceChildren(
    h('a', { class: 'skip', href: '#main' }, t("К содержимому")),
    h('header', { class: 'topbar' },
      h('div', { class: 'brand' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, icon('brand')), h('span', {}, 'Домовой')),
      bars[1],
      h('div', { class: 'topbar-actions' }, languagePill(),
        h('button', { type: 'button', class: 'pill', 'aria-haspopup': 'dialog', 'aria-label': t("Сменить дом"), onClick: openHouses }, icon('home'), icon('chevron-down')))),
    banner, h('main', { class: 'page', id: 'main' }, views.home, views.history, views.house), bars[0]);
  shell = { views, bars, banner, history: null };
}

function renderLoading() {
  const home = shell.views.home;
  home.replaceChildren(skeleton('sk-title'), skeleton('sk-hero'), skeleton('sk-card'), skeleton('sk-card'));
  for (const [name, node] of Object.entries(shell.views)) node.hidden = name !== 'home';
}

function renderActive(force) {
  if (!app.data) return renderLoading();
  const { views } = shell;
  for (const [name, node] of Object.entries(views)) node.hidden = name !== app.view;
  for (const bar of shell.bars) {
    bar.querySelectorAll('.tab').forEach(tab => {
      if (tab.dataset.view === app.view) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    });
  }
  if (app.view === 'home') renderHome(views.home);
  else if (app.view === 'history') {
    shell.history ??= createHistory(views.history);
    shell.history.update();
  } else if (force || !app.sub) renderHouse(views.house);
  syncBack();
  return undefined;
}

function syncBack() {
  telegram.showBack(openSheetCount() > 0 || app.sub !== null || app.view !== 'home');
}

function go(view, sub = null) {
  app.view = view;
  app.sub = view === 'house' ? sub : null;
  renderActive(true);
  window.scrollTo({ top: 0, behavior: 'instant' });
  shell.views[view].querySelector('h1')?.focus({ preventScroll: true });
}

function back() {
  if (openSheetCount()) closeTopSheet();
  else if (app.sub) go('house');
  else go('home');
}

function onData() {
  if (expired) return;
  loadedAt = Date.now();
  if (app.houseId === null && app.houses.length === 0) {
    shownHouse = null;
    showOnboarding();
    return;
  }
  if (!shell) buildShell();
  if (app.houseId !== shownHouse) {
    shownHouse = app.houseId;
    shell.history = null;
    shell.views.history.replaceChildren();
    app.view = 'home';
    app.sub = null;
  }
  renderActive(false);
}

function readContext() {
  try {
    const context = JSON.parse(sessionStorage.getItem(CONTEXT_KEY) || 'null');
    sessionStorage.removeItem(CONTEXT_KEY);
    return context;
  } catch { return null; } // Без хранилища приложение просто открывается на главной.
}

function keepViewportInView() {
  const viewport = window.visualViewport;
  if (!viewport) return;
  const sync = () => document.documentElement.style.setProperty('--vvh', `${viewport.height}px`);
  viewport.addEventListener('resize', sync);
  sync();
}

// Слушатели окна и документа ставятся один раз: «Попробовать ещё раз» вызывает запуск повторно.
function wireOnce() {
  if (wired) return;
  wired = true;
  keepViewportInView();
  const showOffline = offline => { if (shell) shell.banner.hidden = !offline; };
  window.addEventListener('online', () => showOffline(false));
  window.addEventListener('offline', () => showOffline(true));
  window.addEventListener('domovoy:languagechanging', () => {
    try { sessionStorage.setItem(CONTEXT_KEY, JSON.stringify({ house: app.houseId, view: app.view, sub: app.sub })); }
    catch { /* Язык меняется и без хранилища; раздел просто не восстановится. */ }
  });
  document.addEventListener('visibilitychange', () => {
    // Вернулись в приложение спустя время — тихо обновляем данные; сбой сети здесь не повод мешать.
    if (document.visibilityState === 'visible' && app.data && !expired && Date.now() - loadedAt > STALE_AFTER_MS) {
      refresh().catch(error => { if (error.kind === 'session') showExpired(); });
    }
  });
}

async function boot() {
  await initI18n(telegram.user?.language_code);
  document.title = telegram.available ? 'Домовой' : t("Закрытое приложение");
  if (!telegram.available) { showGate(); return; }
  telegram.start();
  app.api = createApi(telegram.initData);
  nav.go = go;
  nav.redraw = redraw;
  telegram.setBackHandler(back);
  configureUi({ sheetsChanged: syncBack, sessionExpired: showExpired });
  wireOnce();
  subscribe(onData);
  const context = readContext();
  buildShell();
  renderLoading();
  try {
    await loadHouses(Number.isSafeInteger(context?.house) && context.house > 0 ? context.house : undefined);
  } catch (error) {
    if (error.kind === 'session') showExpired();
    else showBootError(error);
    return;
  }
  if (app.data && ['home', 'history', 'house'].includes(context?.view)) go(context.view, context.sub ?? null);
}

initTheme();
boot();
