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

function params(page) {
  const query = new URLSearchParams();
  if (app.allMonths) query.set('all_months', 'true');
  else if (app.month) query.set('month', app.month);
  if (app.query.trim()) query.set('q', app.query.trim());
  for (const [key, value] of Object.entries(app.filters)) if (value && value !== 'all') query.set(key, value);
  query.set('page', page);
  return query;
}

export const selectionParams = () => {
  const query = params(0);
  query.delete('page');
  return query;
};

// Загружает первые app.pages страниц журнала (после правки список остаётся той же длины) и обзор дома.
export async function refresh() {
  const house = app.houseId;
  const version = ++loadVersion;
  const stale = () => house !== app.houseId || version !== loadVersion;
  const first = await app.api.get(`houses/${house}?${params(0)}`);
  if (stale()) return;
  const count = Math.max(1, Math.min(app.pages, Math.ceil(first.total / first.page_size)));
  const rest = await Promise.all(Array.from({ length: count - 1 }, (_, index) => app.api.get(`houses/${house}?${params(index + 1)}`)));
  if (stale()) return;
  app.data = first;
  app.month = first.month;
  app.pages = count;
  app.rows = [first.rows, ...rest.map(page => page.rows)].flat();
  emit();
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

export async function loadHouses(preferred) {
  const { houses } = await app.api.get('houses');
  app.houses = houses;
  if (!houses.length) {
    app.houseId = null;
    app.data = null;
    emit();
    return;
  }
  const wanted = [preferred, rememberedHouse()].find(id => houses.some(house => house.id === id));
  await selectHouse(wanted ?? houses[0].id);
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
