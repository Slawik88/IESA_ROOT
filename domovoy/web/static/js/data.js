// Загрузка данных дома: список домов, обзор с учётом фильтров, «Показать ещё». Подписчики получают сигнал после каждой загрузки.
import { app, DEFAULT_FILTERS } from './state.js';

const HOUSE_KEY = 'domovoy.house';
const listeners = new Set();
let loadVersion = 0;

export const subscribe = listener => listeners.add(listener);
const emit = () => listeners.forEach(listener => listener());
// Перерисовать экраны без обращения к серверу (например, после изменения черновика).
export const redraw = emit;

function rememberHouse(id) {
  try { localStorage.setItem(HOUSE_KEY, String(id)); }
  catch { /* Без хранилища дом просто не запоминается. */ }
}

function rememberedHouse() {
  try { return Number(localStorage.getItem(HOUSE_KEY)) || null; }
  catch { return null; }
}

function params(page, span = 1) {
  const query = new URLSearchParams();
  if (app.allMonths) query.set('all_months', 'true');
  else if (app.month) query.set('month', app.month);
  if (app.query.trim()) query.set('q', app.query.trim());
  for (const [key, value] of Object.entries(app.filters)) if (value && value !== 'all') query.set(key, value);
  query.set('page', page);
  if (span > 1) query.set('span', span);
  return query;
}

export const selectionParams = () => {
  const query = params(0);
  query.delete('page');
  return query;
};

function accept(data) {
  app.data = data;
  app.month = data.month;
  app.pages = Math.max(1, Math.min(app.pages, Math.ceil(data.total / data.page_size), data.max_span));
  app.rows = data.rows;
  emit();
}

// Одним запросом загружает обзор дома и первые app.pages страниц журнала (после правки список остаётся той же длины).
export async function refresh() {
  const house = app.houseId;
  const version = ++loadVersion;
  const data = await app.api.get(`houses/${house}?${params(0, Math.min(app.pages, app.data?.max_span ?? 1))}`);
  if (house !== app.houseId || version !== loadVersion) return;
  accept(data);
}

export async function loadMore() {
  const house = app.houseId;
  const next = await app.api.get(`houses/${house}?${params(app.pages)}`);
  if (house !== app.houseId) return;
  app.rows = [...app.rows, ...next.rows];
  app.pages += 1;
  app.data = { ...app.data, total: next.total };
  emit();
}

export async function applySelection(patch) {
  Object.assign(app, patch);
  app.pages = 1;
  await refresh();
}

export function resetSelection() {
  app.filters = { ...DEFAULT_FILTERS };
  app.query = '';
  app.allMonths = false;
  app.month = '';
  app.pages = 1;
}

// Список домов и обзор запомненного дома запрашиваются одновременно: на телефоне это экономит целый круг до сервера.
export async function loadHouses(preferred) {
  resetSelection(); // запрос запомненного дома не должен унаследовать месяц и фильтры прежнего
  const guess = [preferred, rememberedHouse()].find(Boolean);
  const [{ houses }, early] = await Promise.all([
    app.api.get('houses'),
    guess ? app.api.get(`houses/${guess}?${params(0)}`).catch(error => (error.kind === 'session' ? Promise.reject(error) : null)) : null,
  ]);
  app.houses = houses;
  if (!houses.length) {
    app.houseId = null;
    app.data = null;
    emit();
    return;
  }
  const wanted = [preferred, rememberedHouse()].find(id => houses.some(house => house.id === id)) ?? houses[0].id;
  if (early && wanted === guess) {
    app.houseId = wanted;
    rememberHouse(wanted);
    accept(early);
    return;
  }
  await selectHouse(wanted);
}

export async function selectHouse(id) {
  app.houseId = id;
  app.data = null;
  app.rows = [];
  resetSelection();
  rememberHouse(id);
  emit();
  await refresh();
}
