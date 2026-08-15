#!/usr/bin/env node
import fs from 'fs';
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8402';
const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
const source = fs.readFileSync(
  new URL('../FastAPI/static/reconstruction-lab.html', import.meta.url),
  'utf8',
);
const productionHtml = source
  .replace('data-runtime="preview"', 'data-runtime="production"')
  .replace('data-api-base="/__reconstruction"', 'data-api-base=""');

const [manifest, initialState] = await Promise.all([
  fetch(`${base}/__reconstruction/manifest`).then((response) => response.json()),
  fetch(`${base}/__reconstruction/state`, {
    headers: { 'x-reconstruction-session': 'production-adapter-verifier' },
  }).then((response) => response.json()),
]);

const completedState = {
  ...initialState,
  run_id: 77,
  status: 'won',
  outcome_reason: 'all_echoes_broken',
};
const memory = {
  id: 'm_mobile_oath',
  unit_id: manifest.starter_units[0].id,
  name: 'Клятва движения',
  effect: 'Проверочный постоянный выбор.',
  tradeoff: 'Нельзя выбрать второй вариант.',
};
const overview = {
  content: manifest,
  progress: {
    started: true,
    current_encounter: 'e02_shattered_causeway',
    completed: ['e01_two_bells'],
    memories: [],
    pending_memory: { encounter_id: 'e01_two_bells', choices: [memory] },
  },
  active_run: completedState,
  stats: {
    runs_started: 1,
    runs_won: 1,
    runs_lost: 0,
    correct_taps: 8,
    total_taps: 10,
    mistakes: 2,
    missed_signals: 1,
    best_combo: 5,
    fastest_win_ms: 42000,
    total_play_ms: 42000,
    upgrades: {},
  },
};

const browser = await puppeteer.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/production-harness') {
      request.respond({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: productionHtml,
      });
      return;
    }
    if (url.pathname === '/reconstruction' && request.method() === 'GET') {
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(overview),
      });
      return;
    }
    if (url.pathname === '/reconstruction/memory' && request.method() === 'POST') {
      request.respond({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({ ok: true, memory_id: memory.id, idempotent_replay: false }),
      });
      return;
    }
    request.continue();
  });

  await page.goto(`${base}/production-harness`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#resultLayer:not([hidden])');
  const labels = await page.evaluate(() => ({
    runtime: document.getElementById('runtimeEyebrow').textContent.trim(),
    profile: document.getElementById('profileKind').textContent.trim(),
    stats: document.getElementById('statsEyebrow').textContent.trim(),
    statsCopy: document.getElementById('statsCopy').textContent.trim(),
    resultAction: document.getElementById('resultReset').textContent.trim(),
  }));
  if (labels.runtime !== 'БОЕВАЯ СИСТЕМА') throw new Error(`runtime label: ${labels.runtime}`);
  if (labels.profile !== 'ПРОФИЛЬ ИГРОКА') throw new Error(`profile label: ${labels.profile}`);
  if (labels.stats !== 'ПРОФИЛЬ РАЗЛОМА') throw new Error(`stats label: ${labels.stats}`);
  if (!labels.statsCopy.includes('Серверная статистика')) {
    throw new Error(`stats copy is still preview-only: ${labels.statsCopy}`);
  }
  if (!labels.resultAction.includes('Выбрать Память')) {
    throw new Error(`pending memory action is missing: ${labels.resultAction}`);
  }

  await page.click('#resultReset');
  await page.waitForSelector('[data-memory-id]');
  await page.click('[data-memory-id]');
  await page.waitForFunction(
    () => document.getElementById('resultReset')?.textContent.includes('Ещё один забег'),
  );
  const resultStats = await page.$$eval('#resultStats span', (nodes) =>
    nodes.map((node) => node.textContent.trim()));
  if (!resultStats.some((value) => value.includes('пропущено'))) {
    throw new Error(`missed signals absent from result: ${resultStats.join(' | ')}`);
  }
  if (errors.length) throw new Error(`browser errors: ${errors.join(' | ')}`);
  console.log('OK: production adapter labels, server stats and Memory handoff');
} finally {
  await browser.close();
}
